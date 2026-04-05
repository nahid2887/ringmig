#!/usr/bin/env python
"""
Test script to demonstrate the new availability format with day-of-week grouping.
This shows how the payload is now organized by day of week with dates underneath.
"""

import os
import sys
import django
from datetime import datetime, date, timedelta

# Setup Django
sys.path.insert(0, '/c/ringmig2/ringmig/core')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from bokking.models import SessionBooking, ListenerAvailability
from bokking.consumers import _serialize_listener_booking_state, _group_by_day_of_week
from django.contrib.auth import get_user_model

User = get_user_model()

# Find a listener with availability
try:
    listener = User.objects.filter(
        booking_availability__isnull=False
    ).first()
    
    if listener:
        print(f"Testing with listener: {listener.email}")
        print("=" * 80)
        
        state = _serialize_listener_booking_state(listener)
        
        print("\n1. AVAILABILITY_TIME (grouped by day-of-week):")
        print("-" * 80)
        import json
        if state['availability_time']:
            print(json.dumps(state['availability_time'][0], indent=2))
        
        print("\n2. BOOKING_TIME (confirmed bookings grouped by day-of-week):")
        print("-" * 80)
        if state['booking_time']:
            print(json.dumps(state['booking_time'][0], indent=2))
        else:
            print("(No completed bookings)")
        
        print("\n3. PENDING_TIME (unpaid bookings grouped by day-of-week):")
        print("-" * 80)
        if state['pending_time']:
            print(json.dumps(state['pending_time'][0], indent=2))
        else:
            print("(No pending bookings)")
        
        print("\n4. EFFECTIVE_AVAILABILITY (free slots after subtracting bookings, grouped by day-of-week):")
        print("-" * 80)
        if state['effective_availability']:
            print(json.dumps(state['effective_availability'][0], indent=2))
        
        print("\n5. SESSION_BOOKINGS (all non-expired bookings):")
        print("-" * 80)
        if state['session_bookings']:
            print(json.dumps(state['session_bookings'][:1], indent=2))
        else:
            print("(No bookings)")
        
        print("\nNEW FORMAT STRUCTURE:")
        print("""
Day-of-week grouping means the payload now looks like:
{
  "availability_time": [
    {
      "day_of_week": 0,
      "dates": [
        {
          "date": "2026-04-06",
          "slots": [...]
        },
        {
          "date": "2026-04-13",
          "slots": [...]
        }
      ]
    },
    {
      "day_of_week": 1,
      "dates": [...]
    }
  ],
  "booking_time": [...],  // Same grouping
  "pending_time": [...],  // Same grouping
  "effective_availability": [...],  // Same grouping
}

KEY IMPROVEMENTS:
✅ Expired pending bookings are now filtered out
✅ Date range extends to include ALL bookings (not just 7 days)
✅ Data grouped by day-of-week (Monday: [6, 13, 20], Tuesday: [7, 14, 21], etc.)
✅ When a pending booking expires, it's removed from the next broadcast
        """)
    else:
        print("❌ No listener with availability found")
        
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
