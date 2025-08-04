"""
Simple call logger for real-time transcription and summarization.
"""

import json
import uuid
import os
from datetime import datetime
from typing import Dict, List
import aiohttp
from .config import OPENAI_API_KEY, CALL_LOG_DIR

class SimpleCallLogger:
    """Simple call logger that saves transcripts to files and generates summaries."""
    
    def __init__(self, storage_dir: str = CALL_LOG_DIR):
        self.storage_dir = storage_dir
        self.active_calls: Dict[str, Dict] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
    
    def start_call(self) -> str:
        """Start a new call and return the call ID."""
        call_id = str(uuid.uuid4())
        call_data = {
            "id": call_id,
            "start_time": datetime.now().isoformat(),
            "transcript": [],
            "status": "active"
        }
        self.active_calls[call_id] = call_data
        
        # Create transcript file
        transcript_file = os.path.join(self.storage_dir, f"{call_id}_transcript.txt")
        with open(transcript_file, 'w') as f:
            f.write(f"Call started at: {call_data['start_time']}\n")
            f.write("=" * 50 + "\n\n")
        
        print(f"Started call logging: {call_id}")
        return call_id
    
    def add_transcript_entry(self, call_id: str, speaker: str, text: str):
        """Add a transcript entry and save to file immediately."""
        if call_id not in self.active_calls:
            print(f"Warning: Call {call_id} not found")
            return
        
        timestamp = datetime.now().isoformat()
        entry = {
            "speaker": speaker,
            "text": text,
            "timestamp": timestamp
        }
        
        # Add to memory
        self.active_calls[call_id]["transcript"].append(entry)
        
        # Save to file immediately
        transcript_file = os.path.join(self.storage_dir, f"{call_id}_transcript.txt")
        with open(transcript_file, 'a', encoding='utf-8') as f:
            f.write(f"[{timestamp}] {speaker.upper()}: {text}\n")
        
        print(f"Added transcript: {speaker}: {text[:50]}...")
    
    async def end_call_and_summarize(self, call_id: str) -> str:
        """End a call and generate a summary."""
        if call_id not in self.active_calls:
            return "Call not found"
        
        call_data = self.active_calls[call_id]
        call_data["end_time"] = datetime.now().isoformat()
        call_data["status"] = "completed"
        
        # Calculate duration
        start_time = datetime.fromisoformat(call_data["start_time"])
        end_time = datetime.fromisoformat(call_data["end_time"])
        duration = (end_time - start_time).total_seconds()
        call_data["duration_seconds"] = duration
        
        # Generate summary and extract structured data
        summary = await self._generate_summary(call_data)
        structured_data = await self._extract_structured_data(call_data)
        
        call_data["summary"] = summary
        call_data["structured_data"] = structured_data
        
        # Save complete call log
        call_log_file = os.path.join(self.storage_dir, f"{call_id}_complete.json")
        with open(call_log_file, 'w', encoding='utf-8') as f:
            json.dump(call_data, f, indent=2, ensure_ascii=False)
        
        # Save structured data separately for easy access
        structured_file = os.path.join(self.storage_dir, f"{call_id}_structured.json")
        with open(structured_file, 'w', encoding='utf-8') as f:
            json.dump(structured_data, f, indent=2, ensure_ascii=False)
        
        # Remove from active calls
        del self.active_calls[call_id]
        
        print(f"Call {call_id} ended. Duration: {duration:.1f}s")
        return summary
    
    async def _extract_structured_data(self, call_data: Dict) -> Dict:
        """Extract structured data from the conversation using GPT-4o-mini."""
        if not call_data["transcript"]:
            return {
                "name": "",
                "purpose": "",
                "where_from": "",
                "where_to": "",
                "lift": "",
                "how_many_rooms": "",
                "extra_info": ""
            }
        
        # Format transcript
        conversation_text = ""
        for entry in call_data["transcript"]:
            speaker_label = "Customer" if entry["speaker"] == "user" else "Eva"
            conversation_text += f"{speaker_label}: {entry['text']}\n"
        
        prompt = f"""
Extract the following information from this moving company customer service call:

Conversation:
{conversation_text}

Please extract and return ONLY a JSON object with these exact fields:
{{
    "name": "customer's name (if provided)",
    "purpose": "moving purpose (e.g., 'residential move', 'office move')",
    "where_from": "origin city/location",
    "where_to": "destination city/location", 
    "lift": "yes/no (if lift service is needed)",
    "how_many_rooms": "number of rooms (e.g., '3 rooms', 'studio')",
    "extra_info": "any additional important information"
}}

If any information is not available, use empty string "". Return ONLY the JSON object, no other text.
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
                            "content": "You are a data extraction specialist. Extract structured information from conversations and return only valid JSON."
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    "max_tokens": 200,
                    "temperature": 0.1
                }
                
                async with session.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers=headers,
                    json=data
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        content = result["choices"][0]["message"]["content"].strip()
                        
                        # Try to parse JSON from the response
                        try:
                            # Remove any markdown formatting if present
                            if content.startswith("```json"):
                                content = content[7:]
                            if content.endswith("```"):
                                content = content[:-3]
                            
                            structured_data = json.loads(content.strip())
                            return structured_data
                        except json.JSONDecodeError:
                            print(f"Failed to parse JSON from response: {content}")
                            return {
                                "name": "",
                                "purpose": "",
                                "where_from": "",
                                "where_to": "",
                                "lift": "",
                                "how_many_rooms": "",
                                "extra_info": ""
                            }
                    else:
                        error_text = await response.text()
                        print(f"Error extracting structured data: {error_text}")
                        return {
                            "name": "",
                            "purpose": "",
                            "where_from": "",
                            "where_to": "",
                            "lift": "",
                            "how_many_rooms": "",
                            "extra_info": ""
                        }
                        
        except Exception as e:
            print(f"Error extracting structured data: {e}")
            return {
                "name": "",
                "purpose": "",
                "where_from": "",
                "where_to": "",
                "lift": "",
                "how_many_rooms": "",
                "extra_info": ""
            }

    async def _generate_summary(self, call_data: Dict) -> str:
        """Generate a summary using GPT-4o-mini."""
        if not call_data["transcript"]:
            return "No conversation recorded."
        
        # Format transcript
        conversation_text = ""
        for entry in call_data["transcript"]:
            speaker_label = "Customer" if entry["speaker"] == "user" else "Eva"
            conversation_text += f"{speaker_label}: {entry['text']}\n"
        
        prompt = f"""
Please provide a structured summary of this customer service call between Eva (the assistant) and a customer.

Call Duration: {call_data['duration_seconds']:.1f} seconds

Conversation:
{conversation_text}

Please provide a structured summary with:
1. Main Topic/Issue: What was the primary concern?
2. Key Information: What important details were gathered?
3. Actions Taken: What was decided or promised?
4. Outcome: What was the final result?

Keep it concise and professional (2-3 sentences per section).
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
                            "content": "You are a professional call summarizer. Provide clear, structured summaries of customer service calls."
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    "max_tokens": 300,
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
    
    def get_active_call_ids(self) -> List[str]:
        """Get list of active call IDs."""
        return list(self.active_calls.keys())

# Global instance
simple_call_logger = SimpleCallLogger() 