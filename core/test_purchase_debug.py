import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.contrib.auth import get_user_model
from bokking.models import SessionBooking, UniversalBookingPackage, ListenerAvailability, TimeSlot
from datetime import datetime, date, time
from decimal import Decimal

User = get_user_model()

# Check if test data exists
try:
    listener = User.objects.get(id=5)
    print(f"✓ Listener found: {listener.email}")
except User.DoesNotExist:
    print("✗ Listener with ID 5 not found")
    exit(1)

try:
    package = UniversalBookingPackage.objects.get(id=1)
    print(f"✓ Package found: {package.name}")
except UniversalBookingPackage.DoesNotExist:
    print("✗ Package with ID 1 not found")
    exit(1)

# Check listener availability
try:
    avail = ListenerAvailability.objects.get(listener=listener)
    print(f"✓ Listener has availability")
except ListenerAvailability.DoesNotExist:
    print("✗ Listener has no availability schedule")
    exit(1)

# Check time slots
slots = avail.time_slots.all()
print(f"✓ Time slots: {slots.count()}")
for slot in slots:
    print(f"  - {slot}")

# Try checking slot availability
booking_date = date(2026, 4, 29)
start_time = time(3, 44)
is_available, end_time, msg = SessionBooking.check_slot_available(
    listener=listener,
    booking_date=booking_date,
    start_time=start_time,
    duration_minutes=package.duration
)
print(f"\nSlot check: {is_available}")
print(f"  End time: {end_time}")
print(f"  Message: {msg}")

if not is_available:
    print("\n✗ Slot is NOT available - this is likely why the purchase fails")
