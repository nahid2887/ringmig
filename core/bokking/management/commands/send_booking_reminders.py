from django.core.management.base import BaseCommand

from bokking.models import SessionBooking


class Command(BaseCommand):
    help = 'Send 10-minute, 5-minute, and start-time reminder emails to talker and listener for upcoming bookings.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--minutes-before',
            type=int,
            default=None,
            help='Optional single reminder window in minutes before session start. If omitted, sends 10, 5, and 0 minute reminders.'
        )

    def handle(self, *args, **options):
        minutes_before = options['minutes_before']
        if minutes_before is None:
            stats = SessionBooking.send_scheduled_start_reminders()
        else:
            stats = SessionBooking.send_upcoming_start_reminders(minutes_before=minutes_before)

        self.stdout.write(
            self.style.SUCCESS(
                (
                    f"Reminder run completed | processed={stats['processed']} "
                    f"talker_sent={stats['talker_sent']} "
                    f"listener_sent={stats['listener_sent']} failed={stats['failed']}"
                )
            )
        )
