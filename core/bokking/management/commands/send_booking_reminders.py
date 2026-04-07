from django.core.management.base import BaseCommand

from bokking.models import SessionBooking


class Command(BaseCommand):
    help = 'Send 20-minute reminder emails to talker and listener for upcoming bookings.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--minutes-before',
            type=int,
            default=20,
            help='Reminder window in minutes before session start (default: 20).'
        )

    def handle(self, *args, **options):
        minutes_before = options['minutes_before']
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
