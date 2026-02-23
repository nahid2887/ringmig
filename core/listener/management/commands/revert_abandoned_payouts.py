from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from chat.call_models import ListenerPayout

User = get_user_model()


class Command(BaseCommand):
    help = 'Revert pending payouts that have been abandoned for more than 24 hours'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be changed without making changes',
        )
        parser.add_argument(
            '--hours',
            type=int,
            default=24,
            help='Hours after which to consider a pending payout abandoned (default: 24)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        hours = options['hours']
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))
        
        # Find pending payouts older than specified hours
        cutoff_time = timezone.now() - timedelta(hours=hours)
        abandoned_payouts = ListenerPayout.objects.filter(
            status='pending',
            payout_requested_at__lt=cutoff_time
        )
        
        if not abandoned_payouts.exists():
            self.stdout.write(self.style.SUCCESS(f'No abandoned payouts found (older than {hours} hours)'))
            return
        
        self.stdout.write(f"Found {abandoned_payouts.count()} abandoned payouts:")
        
        for payout in abandoned_payouts:
            self.stdout.write(f"  Payout ID {payout.id}: {payout.listener.email} - ${payout.amount} (pending since {payout.payout_requested_at})")
        
        if not dry_run:
            # Revert status from pending back to earned
            updated_count = abandoned_payouts.update(
                status='earned',
                payout_requested_at=None,
                stripe_payout_id='',
                notes='Reverted from abandoned payout request'
            )
            
            self.stdout.write(
                self.style.SUCCESS(f'Successfully reverted {updated_count} abandoned payouts back to "earned" status')
            )
        else:
            self.stdout.write(
                self.style.WARNING(f'Would revert {abandoned_payouts.count()} payouts back to "earned" status')
            )