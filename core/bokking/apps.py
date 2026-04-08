import logging
import os
import threading
import time

from django.apps import AppConfig


logger = logging.getLogger(__name__)
_booking_reminder_scheduler_started = False


def _booking_reminder_scheduler_loop(interval_seconds=60):
    """Run booking reminder and earnings-release checks inside the active server process."""
    from bokking.models import SessionBooking

    while True:
        try:
            stats = SessionBooking.send_upcoming_start_reminders(minutes_before=20)
            if stats.get('processed') or stats.get('talker_sent') or stats.get('listener_sent'):
                logger.info(
                    'Booking reminder tick: processed=%s talker_sent=%s listener_sent=%s failed=%s',
                    stats.get('processed'),
                    stats.get('talker_sent'),
                    stats.get('listener_sent'),
                    stats.get('failed'),
                )

            earnings_stats = SessionBooking.release_ended_listener_earnings()
            if earnings_stats.get('processed') or earnings_stats.get('released') or earnings_stats.get('failed'):
                logger.info(
                    'Booking earnings tick: processed=%s released=%s failed=%s',
                    earnings_stats.get('processed'),
                    earnings_stats.get('released'),
                    earnings_stats.get('failed'),
                )
        except Exception as exc:
            logger.exception('Booking reminder scheduler failed: %s', exc)

        time.sleep(interval_seconds)


class BokkingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'bokking'
    verbose_name = 'Booking & Availability Management'    
    def ready(self):
        """Import signals when app is ready."""
        import bokking.signals  # noqa

        global _booking_reminder_scheduler_started
        if _booking_reminder_scheduler_started:
            return

        if os.environ.get('DISABLE_BOOKING_REMINDER_SCHEDULER') == '1':
            logger.info('Booking reminder scheduler disabled by environment variable')
            return

        _booking_reminder_scheduler_started = True
        reminder_thread = threading.Thread(
            target=_booking_reminder_scheduler_loop,
            kwargs={'interval_seconds': 60},
            daemon=True,
            name='booking-reminder-scheduler',
        )
        reminder_thread.start()
        logger.info('Booking reminder scheduler started (every 60 seconds)')