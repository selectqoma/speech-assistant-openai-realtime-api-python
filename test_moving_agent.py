#!/usr/bin/env python3
"""
Test script for the moving agent functionality.
"""

from moving_agent import (
    create_moving_request, save_client_name, save_move_date,
    save_locations, save_volume, save_floors, set_price_estimate,
    set_requires_on_site_check, complete_request, get_current_request
)

def test_moving_agent():
    """Test the complete moving agent workflow."""
    print("Testing Moving Agent...")
    
    # 1. Create a new moving request
    print("\n1. Creating new moving request...")
    request = create_moving_request()
    request_id = request.id
    print(f"Created request with ID: {request_id}")
    
    # 2. Save move date
    print("\n2. Saving move date...")
    save_move_date(request_id, "Next Friday, December 15th")
    
    # 3. Save locations
    print("\n3. Saving locations...")
    save_locations(request_id, "Amsterdam Central", "Rotterdam South")
    
    # 4. Save volume
    print("\n4. Saving volume...")
    save_volume(request_id, "2-bedroom apartment, furniture and boxes")
    
    # 5. Save floors
    print("\n5. Saving floors...")
    save_floors(request_id, "3rd floor", "1st floor")
    
    # 6. Set price estimate
    print("\n6. Setting price estimate...")
    set_price_estimate(request_id, "€450-550")
    
    # 7. Set on-site check requirement
    print("\n7. Setting on-site check requirement...")
    set_requires_on_site_check(request_id, False)
    
    # 8. Save client name
    print("\n8. Saving client name...")
    save_client_name(request_id, "John Smith")
    
    # 9. Get current request to verify
    print("\n9. Getting current request...")
    current_request = get_current_request(request_id)
    if current_request:
        print(f"Current request status: {current_request.status}")
        print(f"Client: {current_request.client_name}")
        print(f"Move date: {current_request.move_date}")
        print(f"From: {current_request.from_location} ({current_request.from_floor})")
        print(f"To: {current_request.to_location} ({current_request.to_floor})")
        print(f"Volume: {current_request.volume_description}")
        print(f"Needs lift: {current_request.needs_lift}")
        print(f"Price: {current_request.price_estimate}")
        print(f"On-site check needed: {current_request.requires_on_site_check}")
    
    # 10. Complete the request
    print("\n10. Completing request...")
    complete_request(request_id)
    
    print("\n✅ Moving agent test completed successfully!")
    print(f"Request saved to: moving_requests/{request_id}.json")

if __name__ == "__main__":
    test_moving_agent() 