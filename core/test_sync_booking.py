"""Test syncing booking to Cal.com"""
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from booking.models import Booking
from booking.calcom_utils import get_calcom_client

# Check booking 9
booking = Booking.objects.get(id=9)
print(f'Booking {booking.id}: status={booking.status}, is_paid={booking.is_paid}, cal_booking_id={booking.cal_booking_id}')

# Try creating in Cal.com
try:
    client = get_calcom_client(booking.listener)
    print(f'Cal.com client ready. API key exists: {bool(client.api_key)}')
    print(f'Event type cal_id: {booking.event_type.cal_event_type_id}')
    
    cal_booking = client.create_booking(
        event_type_id=int(booking.event_type.cal_event_type_id),
        start_time=booking.start_time,
        attendee_name=booking.talker.full_name,
        attendee_email=booking.talker.email,
        attendee_timezone=booking.timezone,
        notes=booking.talker_notes,
        metadata={
            'talker_id': booking.talker.id,
            'listener_id': booking.listener.id,
            'source': 'ringmig',
            'paid': True
        }
    )
    print(f'SUCCESS! Cal.com response:')
    for k, v in cal_booking.items():
        print(f'  {k}: {v}')
    
    # Update local booking
    cal_id = str(cal_booking.get('id', ''))
    booking.cal_booking_id = cal_id if cal_id else None
    booking.cal_booking_uid = cal_booking.get('uid', '')
    booking.meeting_url = cal_booking.get('meetingUrl', '')
    booking.location = cal_booking.get('location', '')
    booking.save(update_fields=['cal_booking_id', 'cal_booking_uid', 'meeting_url', 'location', 'updated_at'])
    print(f'\nBooking {booking.id} updated:')
    print(f'  cal_booking_id: {booking.cal_booking_id}')
    print(f'  cal_booking_uid: {booking.cal_booking_uid}')
    print(f'  meeting_url: {booking.meeting_url}')
    
except Exception as e:
    import traceback
    print(f'ERROR: {type(e).__name__}: {e}')
    traceback.print_exc()
