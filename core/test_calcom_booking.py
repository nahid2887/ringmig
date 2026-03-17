"""
Test Cal.com API with the provided API key
"""
import django
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from booking.calcom_utils import CalComClient
from datetime import datetime, timedelta

API_KEY = 'cal_live_249a1a8781ebbfd9f924670f9c1f98ac'

def test_calcom():
    client = CalComClient(api_key=API_KEY)
    
    print("=" * 60)
    print("Cal.com API Test with provided API key")
    print("=" * 60)
    
    # Test 1: Authentication
    print("\n1. Testing authentication...")
    try:
        me = client.get_me()
        print(f"   ✅ Authenticated as: {me.get('email')}")
        print(f"      User ID: {me.get('id')}")
        print(f"      Name: {me.get('name', 'N/A')}")
    except Exception as e:
        print(f"   ❌ Auth failed: {e}")
        return
    
    # Test 2: Get existing event types
    print("\n2. Getting existing event types...")
    try:
        event_types = client.get_event_types()
        print(f"   ✅ Found {len(event_types)} event types")
        
        if event_types:
            print("\n   Existing event types:")
            for et in event_types:
                print(f"      - ID: {et.get('id')}, Title: {et.get('title')}, Slug: {et.get('slug')}")
                print(f"        Duration: {et.get('lengthInMinutes')}min")
                
            # Use first event type for booking test
            test_event_id = event_types[0].get('id')
            print(f"\n   Will use event type ID {test_event_id} for booking test")
        else:
            print("   No existing event types found. Need to create one first.")
            return
            
    except Exception as e:
        print(f"   ❌ Failed to get event types: {e}")
        return
    
    # Test 3: Get availability
    print("\n3. Checking availability...")
    try:
        start = datetime.utcnow() + timedelta(days=1)
        end = start + timedelta(days=7)
        
        slots = client.get_availability(
            event_type_id=test_event_id,
            start_date=start,
            end_date=end,
            timezone='UTC'
        )
        print(f"   ✅ Found {len(slots)} available slots")
        if slots:
            print(f"      First slot: {slots[0].get('time')}")
    except Exception as e:
        print(f"   ❌ Failed to get availability: {e}")
    
    # Test 4: Create a test booking
    print("\n4. Creating a test booking...")
    try:
        # Get first available slot
        if slots:
            first_slot = datetime.fromisoformat(slots[0].get('time').replace('Z', '+00:00'))
        else:
            # Use a time tomorrow at 10 AM
            first_slot = datetime.utcnow().replace(hour=10, minute=0, second=0, microsecond=0) + timedelta(days=1)
        
        booking = client.create_booking(
            event_type_id=test_event_id,
            start_time=first_slot,
            attendee_name="Test Talker",
            attendee_email="test@example.com",
            attendee_timezone="UTC",
            notes="Test booking from RingMig integration",
            metadata={
                "talker_id": 999,
                "listener_id": 17,
                "source": "ringmig_test"
            }
        )
        print(f"   ✅ Booking created!")
        print(f"      Booking UID: {booking.get('uid')}")
        print(f"      Start time: {booking.get('startTime')}")
        print(f"      Status: {booking.get('status')}")
        
    except Exception as e:
        print(f"   ❌ Failed to create booking: {e}")
    
    print("\n" + "=" * 60)
    print("Test complete!")
    print("=" * 60)


if __name__ == '__main__':
    test_calcom()
