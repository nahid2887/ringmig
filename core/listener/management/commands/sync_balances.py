from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from decimal import Decimal
from django.db.models import Sum
from listener.models import ListenerBalance
from chat.call_models import ListenerPayout

User = get_user_model()


class Command(BaseCommand):
    help = 'Sync ListenerBalance with ListenerPayout transactions'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be changed without making changes',
        )
        parser.add_argument(
            '--listener-id',
            type=int,
            help='Sync balance for specific listener only',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        listener_id = options.get('listener_id')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))
        
        # Get listeners to process
        if listener_id:
            listeners = User.objects.filter(id=listener_id, user_type='listener')
            if not listeners.exists():
                self.stdout.write(
                    self.style.ERROR(f'Listener with ID {listener_id} not found')
                )
                return
        else:
            listeners = User.objects.filter(user_type='listener')
        
        for listener in listeners:
            self.sync_listener_balance(listener, dry_run)
    
    def sync_listener_balance(self, listener, dry_run):
        """Sync a single listener's balance."""
        
        # Calculate totals from ListenerPayout transactions
        payouts_qs = ListenerPayout.objects.filter(listener=listener)
        
        # Total earned (all statuses except cancelled)
        total_earned = payouts_qs.exclude(status='cancelled').aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0.00')
        
        # Available balance (earned - pending - completed)
        earned = payouts_qs.filter(status='earned').aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0.00')
        
        # Get current ListenerBalance
        balance_account, created = ListenerBalance.objects.get_or_create(
            listener=listener,
            defaults={
                'available_balance': Decimal('0.00'),
                'total_earned': Decimal('0.00')
            }
        )
        
        # Show current vs calculated
        self.stdout.write(f"\n{listener.email} (ID: {listener.id})")
        self.stdout.write(f"  Current ListenerBalance:")
        self.stdout.write(f"    Available: ${balance_account.available_balance}")
        self.stdout.write(f"    Total Earned: ${balance_account.total_earned}")
        
        self.stdout.write(f"  Calculated from ListenerPayout:")
        self.stdout.write(f"    Available: ${earned}")
        self.stdout.write(f"    Total Earned: ${total_earned}")
        
        # Check if sync needed
        needs_sync = (
            balance_account.available_balance != earned or
            balance_account.total_earned != total_earned
        )
        
        if needs_sync:
            if not dry_run:
                balance_account.available_balance = earned
                balance_account.total_earned = total_earned
                balance_account.save(update_fields=['available_balance', 'total_earned', 'updated_at'])
                self.stdout.write(
                    self.style.SUCCESS(f"  ✓ Updated balance for {listener.email}")
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f"  → Would update balance for {listener.email}")
                )
        else:
            self.stdout.write(
                self.style.SUCCESS(f"  ✓ Balance already in sync for {listener.email}")
            )