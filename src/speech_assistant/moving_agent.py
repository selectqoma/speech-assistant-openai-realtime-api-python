import json
import os
from datetime import datetime
from typing import Dict, Optional, Any
from dataclasses import dataclass, asdict
import uuid

from .config import MOVING_REQUESTS_DIR

@dataclass
class MovingRequest:
    """Data structure for moving request information."""
    id: str
    created_at: str
    client_name: Optional[str] = None
    move_date: Optional[str] = None
    from_location: Optional[str] = None
    to_location: Optional[str] = None
    volume_description: Optional[str] = None
    from_floor: Optional[str] = None
    to_floor: Optional[str] = None
    needs_lift: Optional[bool] = None
    price_estimate: Optional[str] = None
    requires_on_site_check: Optional[bool] = None
    status: str = "in_progress"
    notes: Optional[str] = None

class MovingAgent:
    """Agent for managing moving request data collection."""
    
    def __init__(self, storage_dir: str = MOVING_REQUESTS_DIR):
        self.storage_dir = storage_dir
        self.active_requests: Dict[str, MovingRequest] = {}
        self._ensure_storage_dir()
    
    def _ensure_storage_dir(self):
        """Ensure the storage directory exists."""
        os.makedirs(self.storage_dir, exist_ok=True)
    
    def create_moving_request(self) -> MovingRequest:
        """Create a new moving request and return it."""
        request_id = str(uuid.uuid4())
        request = MovingRequest(
            id=request_id,
            created_at=datetime.now().isoformat()
        )
        self.active_requests[request_id] = request
        print(f"Created new moving request: {request_id}")
        return request
    
    def save_client_name(self, request_id: str, name: str) -> bool:
        """Save the client's name."""
        if request_id in self.active_requests:
            self.active_requests[request_id].client_name = name
            print(f"Saved client name: {name}")
            return True
        return False
    
    def save_move_date(self, request_id: str, date: str) -> bool:
        """Save the move date."""
        if request_id in self.active_requests:
            self.active_requests[request_id].move_date = date
            print(f"Saved move date: {date}")
            return True
        return False
    
    def save_locations(self, request_id: str, from_location: str, to_location: str) -> bool:
        """Save the from and to locations."""
        if request_id in self.active_requests:
            self.active_requests[request_id].from_location = from_location
            self.active_requests[request_id].to_location = to_location
            print(f"Saved locations: {from_location} -> {to_location}")
            return True
        return False
    
    def save_volume(self, request_id: str, volume: str) -> bool:
        """Save the volume description."""
        if request_id in self.active_requests:
            self.active_requests[request_id].volume_description = volume
            print(f"Saved volume: {volume}")
            return True
        return False
    
    def save_floors(self, request_id: str, from_floor: str, to_floor: str) -> bool:
        """Save the floor information and determine if lift is needed."""
        if request_id in self.active_requests:
            self.active_requests[request_id].from_floor = from_floor
            self.active_requests[request_id].to_floor = to_floor
            
            # Determine if lift is needed (simple logic - can be enhanced)
            needs_lift = False
            try:
                from_floor_num = int(from_floor.replace("st", "").replace("nd", "").replace("rd", "").replace("th", ""))
                to_floor_num = int(to_floor.replace("st", "").replace("nd", "").replace("rd", "").replace("th", ""))
                needs_lift = from_floor_num > 1 or to_floor_num > 1
            except:
                # If we can't parse, assume lift might be needed
                needs_lift = True
            
            self.active_requests[request_id].needs_lift = needs_lift
            print(f"Saved floors: {from_floor} -> {to_floor}, needs_lift: {needs_lift}")
            return True
        return False
    
    def set_price_estimate(self, request_id: str, estimate: str) -> bool:
        """Set a price estimate."""
        if request_id in self.active_requests:
            self.active_requests[request_id].price_estimate = estimate
            print(f"Saved price estimate: {estimate}")
            return True
        return False
    
    def set_requires_on_site_check(self, request_id: str, requires_check: bool) -> bool:
        """Set whether an on-site check is required."""
        if request_id in self.active_requests:
            self.active_requests[request_id].requires_on_site_check = requires_check
            print(f"Set requires on-site check: {requires_check}")
            return True
        return False
    
    def complete_request(self, request_id: str) -> bool:
        """Mark the request as completed and save to file."""
        if request_id in self.active_requests:
            request = self.active_requests[request_id]
            request.status = "completed"
            
            # Save to file
            filename = f"{self.storage_dir}/{request_id}.json"
            with open(filename, 'w') as f:
                json.dump(asdict(request), f, indent=2)
            
            print(f"Completed and saved request: {request_id}")
            return True
        return False
    
    def get_current_request(self, request_id: str) -> Optional[MovingRequest]:
        """Get the current request by ID."""
        return self.active_requests.get(request_id)
    
    def get_all_requests(self) -> Dict[str, MovingRequest]:
        """Get all active requests."""
        return self.active_requests.copy()
    
    def load_request_from_file(self, request_id: str) -> Optional[MovingRequest]:
        """Load a request from file."""
        filename = f"{self.storage_dir}/{request_id}.json"
        if os.path.exists(filename):
            with open(filename, 'r') as f:
                data = json.load(f)
                return MovingRequest(**data)
        return None

# Global instance
moving_agent = MovingAgent()

# Function exports for Eva to call
def create_moving_request():
    """Create a new moving request."""
    return moving_agent.create_moving_request()

def save_client_name(request_id: str, name: str):
    """Save the client's name."""
    return moving_agent.save_client_name(request_id, name)

def save_move_date(request_id: str, date: str):
    """Save the move date."""
    return moving_agent.save_move_date(request_id, date)

def save_locations(request_id: str, from_location: str, to_location: str):
    """Save the from and to locations."""
    return moving_agent.save_locations(request_id, from_location, to_location)

def save_volume(request_id: str, volume: str):
    """Save the volume description."""
    return moving_agent.save_volume(request_id, volume)

def save_floors(request_id: str, from_floor: str, to_floor: str):
    """Save the floor information."""
    return moving_agent.save_floors(request_id, from_floor, to_floor)

def set_price_estimate(request_id: str, estimate: str):
    """Set a price estimate."""
    return moving_agent.set_price_estimate(request_id, estimate)

def set_requires_on_site_check(request_id: str, requires_check: bool):
    """Set whether an on-site check is required."""
    return moving_agent.set_requires_on_site_check(request_id, requires_check)

def complete_request(request_id: str):
    """Complete the request and save to file."""
    return moving_agent.complete_request(request_id)

def get_current_request(request_id: str):
    """Get the current request by ID."""
    return moving_agent.get_current_request(request_id) 